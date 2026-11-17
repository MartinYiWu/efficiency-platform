package com.aiep.aihub.memory;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MemoryRestoreMapperTest {
 @Test void restoreGateFragmentsResolveAcrossBothMapperNamespaces()throws Exception{
  var configuration=new Configuration();
  for(String resource:List.of("mapper/memory/MemoryMapper.xml","mapper/memory/MemoryPacketMapper.xml")){
   try(var stream=Resources.getResourceAsStream(resource)){
    new XMLMapperBuilder(stream,configuration,resource,configuration.getSqlFragments()).parse();
   }
  }
  var source=configuration.getMappedStatement("com.aiep.aihub.repository.memory.MemoryPacketMapper.findSource");
  var sql=source.getBoundSql(Map.of("tenant",new byte[]{1},"id",new byte[]{2})).getSql();
  assertTrue(sql.contains("ai_memory_tombstone"));assertTrue(sql.contains("ai_memory_suppression"));
  assertNotNull(configuration.getMappedStatement("com.aiep.aihub.repository.memory.MemoryMapper.findPreferenceVersion"));
  assertNotNull(configuration.getMappedStatement("com.aiep.aihub.repository.memory.MemoryMapper.listPreferenceVersions"));
 }
}
